// Twin: first word 8'h69 at prescale 1, but the second word 8'h96 is received
// at the next prescale value up (16'd2).
module cov_P11_twin (
  input logic        clk,
  input logic        rst,
  input logic [15:0] prescale,
  input logic [18:0] prescale_reg,
  input logic [3:0]  bit_cnt,
  input logic        rxd_reg,
  input logic        busy,
  input logic        frame_error,
  input logic        m_axis_tvalid,
  input logic [7:0]  m_axis_tdata
);

  reg ok1;         // current frame at prescale 1
  reg ok2;         // current frame at prescale 2
  reg first_done;  // a prescale-1 word 8'h69 was delivered

  always @(posedge clk) begin
    if (rst) begin
      ok1        <= 1'b0;
      ok2        <= 1'b0;
      first_done <= 1'b0;
    end else begin
      if (prescale_reg == 19'd0 && bit_cnt == 4'd0 && !rxd_reg) begin
        ok1 <= (prescale == 16'd1);
        ok2 <= (prescale == 16'd2);
      end else if (busy) begin
        if (prescale != 16'd1 || frame_error) ok1 <= 1'b0;
        if (prescale != 16'd2 || frame_error) ok2 <= 1'b0;
      end

      if (frame_error) begin
        first_done <= 1'b0;
      end else if (m_axis_tvalid && !$past(m_axis_tvalid)) begin
        if (ok1 && m_axis_tdata == 8'h69) first_done <= 1'b1;
        else first_done <= 1'b0;
      end
    end
  end

  P11_twin_rx_second_word_prescale2: cover property (@(posedge clk) disable iff (rst)
    first_done && ok2 && (prescale == 16'd2) && !frame_error &&
    $rose(m_axis_tvalid) && (m_axis_tdata == 8'h96));

endmodule

bind uart_rx cov_P11_twin u_cov_P11_twin (.*);
