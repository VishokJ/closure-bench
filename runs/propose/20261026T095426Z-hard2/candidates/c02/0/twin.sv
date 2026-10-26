// Twin: rxd_reg is still high at the frame_error pulse, so the receiver goes
// idle and the new start bit is only picked up one clock later; that frame
// then completes with 8'hA5.
module cov_P2_twin (
  input logic       clk,
  input logic       rst,
  input logic       frame_error,
  input logic       rxd_reg,
  input logic [3:0] bit_cnt,
  input logic       m_axis_tvalid,
  input logic [7:0] m_axis_tdata
);

  reg [1:0] tst;

  always @(posedge clk) begin
    if (rst) begin
      tst <= 2'd0;
    end else begin
      if (tst == 2'd1) begin
        if (!rxd_reg) tst <= 2'd2;
        else tst <= 2'd0;
      end else if (tst == 2'd2) begin
        if (bit_cnt == 4'd0) tst <= 2'd0;
      end
      if (frame_error && rxd_reg) begin
        tst <= 2'd1;
      end
    end
  end

  P2_twin_rx_late_restart_after_frame_error: cover property (@(posedge clk) disable iff (rst)
    (tst == 2'd2) && $rose(m_axis_tvalid) && (m_axis_tdata == 8'hA5));

endmodule

bind uart_rx cov_P2_twin u_cov_P2_twin (.*);
