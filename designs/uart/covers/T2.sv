module cov_T2 (
  input logic        clk,
  input logic        rst,
  input logic [15:0] prescale,
  input logic [18:0] prescale_reg,
  input logic [3:0]  bit_cnt,
  input logic        txd,
  input logic        s_axis_tvalid,
  input logic [7:0]  s_axis_tdata
);

  reg [7:0] shift;
  reg       active;
  reg       done;

  always @(posedge clk) begin
    if (rst) begin
      shift  <= 8'h00;
      active <= 1'b0;
      done   <= 1'b0;
    end else begin
      done <= 1'b0;
      if (prescale_reg == 19'd0 && bit_cnt == 4'd0 && s_axis_tvalid) begin
        // a new frame is loaded on this edge
        active <= (prescale == 16'hFFFF);
        shift  <= 8'h00;
      end else if (active && prescale_reg == 19'd0 && bit_cnt != 4'd0 && bit_cnt <= 4'd8) begin
        // at a bit boundary txd still holds the data bit that is ending
        shift <= {txd, shift[7:1]};
        if (bit_cnt == 4'd1) begin
          done   <= 1'b1;
          active <= 1'b0;
        end
      end
      if (prescale != 16'hFFFF) begin
        active <= 1'b0;
      end
    end
  end

  T2_tx_max_prescale_5a: cover property (@(posedge clk) disable iff (rst)
    done && shift == 8'h5A && prescale_reg == 19'h7FFF8 && bit_cnt == 4'd0 &&
    txd && prescale == 16'hFFFF);

endmodule

bind uart_tx cov_T2 u_cov_T2 (.*);
