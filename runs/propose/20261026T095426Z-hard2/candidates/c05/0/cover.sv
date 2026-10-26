// Run-time baud change between frames: word 8'hA5 delivered at prescale 1,
// prescale changed to 2 while the receiver is idle (busy low), then the next
// delivered word is 8'h5A at prescale 2 with no frame error in between.
// (Prescale 2 rather than 3 keeps both frames within the formal bound; it
// still toggles prescale[1].)
module cov_P5 (
  input logic        clk,
  input logic        rst,
  input logic [15:0] prescale,
  input logic        busy,
  input logic        m_axis_tvalid,
  input logic [7:0]  m_axis_tdata,
  input logic        frame_error
);

  // 0: idle; 1: 8'hA5 delivered at prescale 1; 2: prescale changed to 2 while idle
  reg [1:0] st;

  always @(posedge clk) begin
    if (rst) begin
      st <= 2'd0;
    end else begin
      if ($rose(m_axis_tvalid) && (m_axis_tdata == 8'hA5) && (prescale == 16'd1)) begin
        st <= 2'd1;
      end else if (st == 2'd1) begin
        if ($rose(m_axis_tvalid) || frame_error) begin
          st <= 2'd0;
        end else if (prescale == 16'd2 && !busy) begin
          st <= 2'd2;
        end else if (prescale != 16'd1) begin
          st <= 2'd0;
        end
      end else if (st == 2'd2) begin
        if (frame_error || (prescale != 16'd2) || $rose(m_axis_tvalid)) begin
          st <= 2'd0;
        end
      end
    end
  end

  P5_rx_prescale_change_between_frames: cover property (@(posedge clk) disable iff (rst)
    (st == 2'd2) && $rose(m_axis_tvalid) && (m_axis_tdata == 8'h5A) &&
    (prescale == 16'd2) && !frame_error);

endmodule

bind uart_rx cov_P5 u_cov_P5 (.*);
